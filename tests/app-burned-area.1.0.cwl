$graph:
  - baseCommand: burned-area
    class: CommandLineTool
    id: main
    inputs:
      pre_event:
        inputBinding:
          position: 1
          prefix: --pre_event
        type: Directory
      post_event:
        inputBinding:
          position: 2
          prefix: --post_event
        type: Directory
      ndvi_threshold:
        inputBinding:
          position: 3
          prefix: --ndvi_threshold
        type: string?
      ndwi_threshold:
        inputBinding:
          position: 4
          prefix: --ndwi_threshold
        type: string?
    outputs:
      results:
        outputBinding:
          glob: .
        type: Directory
    requirements:
      EnvVarRequirement:
        envDef:
          PATH: /srv/conda/envs/env_burned_area/bin:/home/fbrito/.local/bin:/srv/conda/bin:/srv/conda/condabin:/home/fbrito/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/usr/games:/usr/local/games:/snap/bin
      ResourceRequirement: {}
      InlineJavascriptRequirement: {}
      DockerRequirement:
        dockerPull: docker.pkg.github.com/eoepca/app-burned-area/burned-area:1.0
  - class: Workflow
    doc: Burned area detection based on NDVI/NDWI thresholds
    id: burned-area
    inputs:
      pre_event:
        doc: Pre event input product reference
        label: Pre event input product reference
        type: Directory
      post_event:
        doc: Post event input product reference
        label: Post event input product reference
        type: Directory
      ndvi_threshold:
        doc: NDVI threshold
        label: NDVI threshold
        type: string?
      ndwi_threshold:
        doc: NDWI threshold
        label: NDWI threshold
        type: string?
    label: Burned area
    outputs:
      - id: wf_outputs
        outputSource:
          - step_1/results
        type: Directory
    steps:
      step_1:
        in:
          pre_event: pre_event
          post_event: post_event
          ndvi_threshold: ndvi_threshold
          ndwi_threshold: ndwi_threshold
        out:
          - results
        run: '#main'
$namespaces:
  s: https://schema.org/
s:softwareVersion: 1.0
cwlVersion: v1.0
schemas:
  - http://schema.org/version/9.0/schemaorg-current-http.rdf
